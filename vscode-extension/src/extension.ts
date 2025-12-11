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
 * 缓存 prompts 数据以提高性能
 */
interface PromptsCache {
    singleFile: PromptsYaml | null;
    singleFileMtime: number;
    multiFilePrompts: Map<string, PromptData>;
}

let cache: PromptsCache = {
    singleFile: null,
    singleFileMtime: 0,
    multiFilePrompts: new Map(),
};

/**
 * 激活扩展
 */
export function activate(context: vscode.ExtensionContext): void {
    console.log('prompt-vcs-hover extension activated');

    const promptDataProvider = new PromptDataProvider();

    // 注册 HoverProvider
    const hoverProvider = vscode.languages.registerHoverProvider(
        { language: 'python', scheme: 'file' },
        new PromptHoverProvider(promptDataProvider)
    );

    // 注册 DefinitionProvider (Go to Definition)
    const definitionProvider = vscode.languages.registerDefinitionProvider(
        { language: 'python', scheme: 'file' },
        new PromptDefinitionProvider(promptDataProvider)
    );

    // 注册 CompletionItemProvider (自动补全)
    const completionProvider = vscode.languages.registerCompletionItemProvider(
        { language: 'python', scheme: 'file' },
        new PromptCompletionProvider(promptDataProvider),
        '"', "'"  // 触发字符
    );

    // 监听文件变化以清除缓存
    const fileWatcher = vscode.workspace.createFileSystemWatcher('**/prompts.yaml');
    fileWatcher.onDidChange(() => {
        cache.singleFile = null;
        cache.singleFileMtime = 0;
    });
    fileWatcher.onDidDelete(() => {
        cache.singleFile = null;
        cache.singleFileMtime = 0;
    });

    context.subscriptions.push(
        hoverProvider,
        definitionProvider,
        completionProvider,
        fileWatcher
    );
}

/**
 * 停用扩展
 */
export function deactivate(): void {
    console.log('prompt-vcs-hover extension deactivated');
    cache = {
        singleFile: null,
        singleFileMtime: 0,
        multiFilePrompts: new Map(),
    };
}

/**
 * Prompt 数据提供器 - 统一处理单文件和多文件模式
 */
class PromptDataProvider {
    private readonly pFunctionRegex = /p\s*\(\s*['"]([^'"]+)['"]/g;

    /**
     * 获取工作区根目录
     */
    getWorkspaceRoot(): string | null {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            return null;
        }
        return workspaceFolders[0].uri.fsPath;
    }

    /**
     * 判断是否为单文件模式
     */
    isSingleFileMode(): boolean {
        const workspaceRoot = this.getWorkspaceRoot();
        if (!workspaceRoot) {
            return false;
        }
        return fs.existsSync(path.join(workspaceRoot, 'prompts.yaml'));
    }

    /**
     * 获取所有可用的 prompt IDs
     */
    getAllPromptIds(): string[] {
        const workspaceRoot = this.getWorkspaceRoot();
        if (!workspaceRoot) {
            return [];
        }

        const ids: string[] = [];

        // 单文件模式
        const promptsFilePath = path.join(workspaceRoot, 'prompts.yaml');
        if (fs.existsSync(promptsFilePath)) {
            try {
                const content = fs.readFileSync(promptsFilePath, 'utf-8');
                const prompts = yaml.load(content) as PromptsYaml;
                if (prompts && typeof prompts === 'object') {
                    ids.push(...Object.keys(prompts));
                }
            } catch {
                // 忽略解析错误
            }
        }

        // 多文件模式
        const promptsDir = path.join(workspaceRoot, 'prompts');
        if (fs.existsSync(promptsDir) && fs.statSync(promptsDir).isDirectory()) {
            try {
                const entries = fs.readdirSync(promptsDir, { withFileTypes: true });
                for (const entry of entries) {
                    if (entry.isDirectory()) {
                        ids.push(entry.name);
                    }
                }
            } catch {
                // 忽略读取错误
            }
        }

        return [...new Set(ids)]; // 去重
    }

    /**
     * 获取指定 prompt 的数据
     */
    getPromptData(key: string): PromptData | null {
        const workspaceRoot = this.getWorkspaceRoot();
        if (!workspaceRoot) {
            return null;
        }

        // 优先从单文件模式获取
        const promptsFilePath = path.join(workspaceRoot, 'prompts.yaml');
        if (fs.existsSync(promptsFilePath)) {
            const data = this.getFromSingleFile(promptsFilePath, key);
            if (data) {
                return data;
            }
        }

        // 尝试多文件模式
        return this.getFromMultiFile(workspaceRoot, key);
    }

    /**
     * 获取 prompt 定义的文件位置
     */
    getPromptLocation(key: string): { uri: vscode.Uri; line: number } | null {
        const workspaceRoot = this.getWorkspaceRoot();
        if (!workspaceRoot) {
            return null;
        }

        // 单文件模式
        const promptsFilePath = path.join(workspaceRoot, 'prompts.yaml');
        if (fs.existsSync(promptsFilePath)) {
            const line = this.findKeyLineInYaml(promptsFilePath, key);
            if (line >= 0) {
                return {
                    uri: vscode.Uri.file(promptsFilePath),
                    line: line,
                };
            }
        }

        // 多文件模式
        const promptDir = path.join(workspaceRoot, 'prompts', key);
        if (fs.existsSync(promptDir)) {
            // 优先查找 v1.yaml
            const v1Path = path.join(promptDir, 'v1.yaml');
            if (fs.existsSync(v1Path)) {
                return {
                    uri: vscode.Uri.file(v1Path),
                    line: 0,
                };
            }
            // 否则查找任意 yaml 文件
            const files = fs.readdirSync(promptDir).filter(f => f.endsWith('.yaml'));
            if (files.length > 0) {
                return {
                    uri: vscode.Uri.file(path.join(promptDir, files[0])),
                    line: 0,
                };
            }
        }

        return null;
    }

    /**
     * 在 YAML 文件中查找 key 所在行
     */
    private findKeyLineInYaml(filePath: string, key: string): number {
        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const lines = content.split('\n');
            const keyPattern = new RegExp(`^${key}\\s*:`);
            for (let i = 0; i < lines.length; i++) {
                if (keyPattern.test(lines[i])) {
                    return i;
                }
            }
        } catch {
            // 忽略错误
        }
        return -1;
    }

    /**
     * 从单文件模式获取 prompt
     */
    private getFromSingleFile(filePath: string, key: string): PromptData | null {
        try {
            const stat = fs.statSync(filePath);
            const mtime = stat.mtimeMs;

            // 使用缓存
            if (cache.singleFile && cache.singleFileMtime === mtime) {
                const value = cache.singleFile[key];
                return this.parsePromptValue(value);
            }

            // 重新加载
            const content = fs.readFileSync(filePath, 'utf-8');
            const prompts = yaml.load(content) as PromptsYaml;

            if (prompts && typeof prompts === 'object') {
                cache.singleFile = prompts;
                cache.singleFileMtime = mtime;

                const value = prompts[key];
                return this.parsePromptValue(value);
            }
        } catch (error) {
            console.error('[prompt-vcs] Failed to parse prompts.yaml:', error);
        }
        return null;
    }

    /**
     * 从多文件模式获取 prompt
     */
    private getFromMultiFile(workspaceRoot: string, key: string): PromptData | null {
        const promptDir = path.join(workspaceRoot, 'prompts', key);
        if (!fs.existsSync(promptDir)) {
            return null;
        }

        // 优先读取 v1.yaml
        const v1Path = path.join(promptDir, 'v1.yaml');
        if (fs.existsSync(v1Path)) {
            return this.readYamlFile(v1Path);
        }

        // 读取目录中的第一个 yaml 文件
        try {
            const files = fs.readdirSync(promptDir).filter(f => f.endsWith('.yaml'));
            if (files.length > 0) {
                return this.readYamlFile(path.join(promptDir, files[0]));
            }
        } catch {
            // 忽略错误
        }

        return null;
    }

    /**
     * 读取单个 YAML 文件
     */
    private readYamlFile(filePath: string): PromptData | null {
        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const data = yaml.load(content) as { template?: string; description?: string };
            if (data && typeof data.template === 'string') {
                return {
                    template: data.template,
                    description: data.description,
                };
            }
        } catch {
            // 忽略错误
        }
        return null;
    }

    /**
     * 解析 prompt 值
     */
    private parsePromptValue(value: unknown): PromptData | null {
        if (value === undefined || value === null) {
            return null;
        }

        if (typeof value === 'string') {
            return { template: value };
        }

        if (typeof value === 'object') {
            const obj = value as PromptData;
            if (typeof obj.template === 'string') {
                return {
                    template: obj.template,
                    description: obj.description,
                };
            }
        }

        return null;
    }

    /**
     * 在行文本中查找光标位置对应的 key
     */
    findKeyAtPosition(
        lineText: string,
        cursorPosition: number
    ): { key: string; startIndex: number; endIndex: number } | null {
        this.pFunctionRegex.lastIndex = 0;

        let match: RegExpExecArray | null;
        while ((match = this.pFunctionRegex.exec(lineText)) !== null) {
            const fullMatchStart = match.index;
            const fullMatchEnd = match.index + match[0].length;

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
}

/**
 * Prompt 悬停提供器
 */
class PromptHoverProvider implements vscode.HoverProvider {
    constructor(private readonly dataProvider: PromptDataProvider) { }

    public provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken
    ): vscode.Hover | null {
        try {
            const lineText = document.lineAt(position.line).text;
            const keyInfo = this.dataProvider.findKeyAtPosition(lineText, position.character);
            if (!keyInfo) {
                return null;
            }

            const promptData = this.dataProvider.getPromptData(keyInfo.key);
            if (!promptData) {
                // 显示 "未找到" 提示
                const md = new vscode.MarkdownString();
                md.appendMarkdown(`**Prompt: \`${keyInfo.key}\`**\n\n`);
                md.appendMarkdown(`⚠️ *未在 prompts.yaml 或 prompts/ 目录中找到*`);
                return new vscode.Hover(md);
            }

            const hoverContent = this.buildHoverContent(keyInfo.key, promptData);
            const range = new vscode.Range(
                position.line,
                keyInfo.startIndex,
                position.line,
                keyInfo.endIndex
            );

            return new vscode.Hover(hoverContent, range);
        } catch (error) {
            console.error('[prompt-vcs-hover] Error:', error);
            return null;
        }
    }

    private buildHoverContent(key: string, data: PromptData): vscode.MarkdownString {
        const md = new vscode.MarkdownString();
        md.isTrusted = true;

        md.appendMarkdown(`**Prompt: \`${key}\`**\n\n`);

        if (data.description) {
            md.appendMarkdown(`*${data.description}*\n\n`);
        }

        md.appendMarkdown('```\n');
        md.appendText(data.template);
        if (!data.template.endsWith('\n')) {
            md.appendText('\n');
        }
        md.appendMarkdown('```');

        return md;
    }
}

/**
 * Prompt 定义跳转提供器 (Go to Definition)
 */
class PromptDefinitionProvider implements vscode.DefinitionProvider {
    constructor(private readonly dataProvider: PromptDataProvider) { }

    public provideDefinition(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken
    ): vscode.Definition | null {
        try {
            const lineText = document.lineAt(position.line).text;
            const keyInfo = this.dataProvider.findKeyAtPosition(lineText, position.character);
            if (!keyInfo) {
                return null;
            }

            const location = this.dataProvider.getPromptLocation(keyInfo.key);
            if (!location) {
                return null;
            }

            return new vscode.Location(
                location.uri,
                new vscode.Position(location.line, 0)
            );
        } catch (error) {
            console.error('[prompt-vcs] Definition error:', error);
            return null;
        }
    }
}

/**
 * Prompt 自动补全提供器
 */
class PromptCompletionProvider implements vscode.CompletionItemProvider {
    constructor(private readonly dataProvider: PromptDataProvider) { }

    public provideCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken,
        _context: vscode.CompletionContext
    ): vscode.CompletionItem[] | null {
        try {
            const lineText = document.lineAt(position.line).text;
            const textBefore = lineText.substring(0, position.character);

            // 检查是否在 p(" 或 p(' 之后
            if (!/p\s*\(\s*['"]$/.test(textBefore)) {
                return null;
            }

            const promptIds = this.dataProvider.getAllPromptIds();
            if (promptIds.length === 0) {
                return null;
            }

            return promptIds.map(id => {
                const item = new vscode.CompletionItem(id, vscode.CompletionItemKind.Value);
                item.detail = 'Prompt ID';

                // 获取 prompt 数据以显示描述
                const data = this.dataProvider.getPromptData(id);
                if (data) {
                    item.documentation = new vscode.MarkdownString(
                        data.description
                            ? `*${data.description}*\n\n\`\`\`\n${data.template}\n\`\`\``
                            : `\`\`\`\n${data.template}\n\`\`\``
                    );
                }

                return item;
            });
        } catch (error) {
            console.error('[prompt-vcs] Completion error:', error);
            return null;
        }
    }
}
