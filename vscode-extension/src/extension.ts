import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';

/**
 * prompts.yaml 中的 Prompt 数据结构
 * 支持两种格式：
 * - 格式 A: 直接字符串 - key: "内容"
 * - 格式 B: 对象结构 - key: { template: "内容", description: "描述" }
 */
interface PromptData {
    template: string;
    description?: string;
}

type PromptsYaml = Record<string, string | PromptData>;

/**
 * 激活扩展
 */
export function activate(context: vscode.ExtensionContext): void {
    console.log('prompt-vcs-hover extension activated');

    // 注册 HoverProvider，仅针对 Python 文件
    const hoverProvider = vscode.languages.registerHoverProvider(
        { language: 'python', scheme: 'file' },
        new PromptHoverProvider()
    );

    context.subscriptions.push(hoverProvider);
}

/**
 * 停用扩展
 */
export function deactivate(): void {
    console.log('prompt-vcs-hover extension deactivated');
}

/**
 * Prompt 悬停提供器
 */
class PromptHoverProvider implements vscode.HoverProvider {
    /**
     * 匹配 p("key") 或 p('key') 的正则表达式
     * 捕获组 1: key 名称
     */
    private readonly pFunctionRegex = /p\s*\(\s*['"]([^'"]+)['"]/g;

    public provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken
    ): vscode.Hover | null {
        try {
            // 获取当前行文本
            const lineText = document.lineAt(position.line).text;

            // 查找当前位置是否在 p("key") 调用中
            const keyInfo = this.findKeyAtPosition(lineText, position.character);
            if (!keyInfo) {
                return null;
            }

            // 读取 prompts.yaml
            const promptData = this.getPromptData(keyInfo.key);
            if (!promptData) {
                return null;
            }

            // 构建 Hover 内容
            const hoverContent = this.buildHoverContent(keyInfo.key, promptData);

            // 创建高亮范围
            const range = new vscode.Range(
                position.line,
                keyInfo.startIndex,
                position.line,
                keyInfo.endIndex
            );

            return new vscode.Hover(hoverContent, range);
        } catch (error) {
            // 静默处理错误，不中断用户体验
            console.error('[prompt-vcs-hover] Error:', error);
            return null;
        }
    }

    /**
     * 在行文本中查找光标位置对应的 key
     */
    private findKeyAtPosition(
        lineText: string,
        cursorPosition: number
    ): { key: string; startIndex: number; endIndex: number } | null {
        // 重置正则状态
        this.pFunctionRegex.lastIndex = 0;

        let match: RegExpExecArray | null;
        while ((match = this.pFunctionRegex.exec(lineText)) !== null) {
            const fullMatchStart = match.index;
            const fullMatchEnd = match.index + match[0].length;

            // 检查光标是否在匹配范围内
            if (cursorPosition >= fullMatchStart && cursorPosition <= fullMatchEnd) {
                return {
                    key: match[1],
                    startIndex: fullMatchStart,
                    endIndex: fullMatchEnd,
                };
            }
        }

        return null;
    }

    /**
     * 从 prompts.yaml 获取 Prompt 数据
     */
    private getPromptData(key: string): PromptData | null {
        // 获取工作区根目录
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            return null;
        }

        const workspaceRoot = workspaceFolders[0].uri.fsPath;
        const promptsFilePath = path.join(workspaceRoot, 'prompts.yaml');

        // 检查文件是否存在
        if (!fs.existsSync(promptsFilePath)) {
            return null;
        }

        try {
            // 读取并解析 YAML
            const fileContent = fs.readFileSync(promptsFilePath, 'utf-8');
            const prompts = yaml.load(fileContent) as PromptsYaml;

            if (!prompts || typeof prompts !== 'object') {
                return null;
            }

            const value = prompts[key];
            if (value === undefined) {
                return null;
            }

            // 兼容两种格式
            if (typeof value === 'string') {
                // 格式 A: 直接字符串
                return { template: value };
            } else if (typeof value === 'object' && value !== null) {
                // 格式 B: 对象结构
                const promptObj = value as PromptData;
                if (typeof promptObj.template === 'string') {
                    return {
                        template: promptObj.template,
                        description: promptObj.description,
                    };
                }
            }

            return null;
        } catch (error) {
            console.error('[prompt-vcs-hover] Failed to parse prompts.yaml:', error);
            return null;
        }
    }

    /**
     * 构建 Hover 显示内容
     */
    private buildHoverContent(
        key: string,
        data: PromptData
    ): vscode.MarkdownString {
        const md = new vscode.MarkdownString();
        md.isTrusted = true;

        // 标题
        md.appendMarkdown(`**Prompt: \`${key}\`**\n\n`);

        // 描述（如果有）
        if (data.description) {
            md.appendMarkdown(`*${data.description}*\n\n`);
        }

        // Prompt 模板内容（代码块格式）
        md.appendMarkdown('```\n');
        md.appendText(data.template);
        if (!data.template.endsWith('\n')) {
            md.appendText('\n');
        }
        md.appendMarkdown('```');

        return md;
    }
}
