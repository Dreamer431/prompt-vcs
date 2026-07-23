import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import {
    findPromptCallAtPosition,
    PromptData,
    PromptsYaml,
    selectPromptFromYaml,
} from './promptUtils';

/**
 * 缓存 prompts 数据以提高性能
 */
interface PromptsCache {
    singleFile: PromptsYaml | null;
    singleFileMtime: number;
    lockfile: Record<string, string> | null;
    lockfileMtime: number;
}

const caches = new Map<string, PromptsCache>();

function getCache(workspaceRoot: string): PromptsCache {
    let cache = caches.get(workspaceRoot);
    if (!cache) {
        cache = {
            singleFile: null,
            singleFileMtime: 0,
            lockfile: null,
            lockfileMtime: 0,
        };
        caches.set(workspaceRoot, cache);
    }
    return cache;
}

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
    fileWatcher.onDidCreate(() => caches.clear());
    fileWatcher.onDidChange(() => caches.clear());
    fileWatcher.onDidDelete(() => caches.clear());

    const lockfileWatcher = vscode.workspace.createFileSystemWatcher('**/.prompt_lock.json');
    lockfileWatcher.onDidCreate(() => caches.clear());
    lockfileWatcher.onDidChange(() => caches.clear());
    lockfileWatcher.onDidDelete(() => caches.clear());

    context.subscriptions.push(
        hoverProvider,
        definitionProvider,
        completionProvider,
        fileWatcher,
        lockfileWatcher
    );
}

/**
 * 停用扩展
 */
export function deactivate(): void {
    console.log('prompt-vcs-hover extension deactivated');
    caches.clear();
}

/**
 * Prompt 数据提供器 - 统一处理单文件和多文件模式
 */
class PromptDataProvider {
    private readonly lockfileName = '.prompt_lock.json';

    /**
     * 获取工作区根目录
     */
    getWorkspaceRoot(resource?: vscode.Uri): string | null {
        if (resource) {
            const resourceFolder = vscode.workspace.getWorkspaceFolder(resource);
            if (resourceFolder) {
                return resourceFolder.uri.fsPath;
            }
        }
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            return null;
        }
        return workspaceFolders[0].uri.fsPath;
    }

    /**
     * 判断是否为单文件模式
     */
    isSingleFileMode(resource?: vscode.Uri): boolean {
        const workspaceRoot = this.getWorkspaceRoot(resource);
        if (!workspaceRoot) {
            return false;
        }
        return fs.existsSync(path.join(workspaceRoot, 'prompts.yaml'));
    }

    /**
     * 获取所有可用的 prompt IDs
     */
    getAllPromptIds(resource?: vscode.Uri): string[] {
        const workspaceRoot = this.getWorkspaceRoot(resource);
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
                    for (const key of Object.keys(prompts)) {
                        if (key.includes('@')) {
                            ids.push(key.split('@', 1)[0]);
                        } else {
                            ids.push(key);
                        }
                    }
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
    getPromptData(key: string, resource?: vscode.Uri): PromptData | null {
        const workspaceRoot = this.getWorkspaceRoot(resource);
        if (!workspaceRoot) {
            return null;
        }

        const lockedVersion = this.getLockedVersion(key, resource);

        // 优先从单文件模式获取
        const promptsFilePath = path.join(workspaceRoot, 'prompts.yaml');
        if (fs.existsSync(promptsFilePath)) {
            const data = this.getFromSingleFile(promptsFilePath, key, lockedVersion || undefined);
            if (data) {
                return data;
            }
        }

        // 尝试多文件模式
        return this.getFromMultiFile(workspaceRoot, key, lockedVersion || undefined);
    }

    /**
     * 获取 prompt 定义的文件位置
     */
    getPromptLocation(
        key: string,
        resource?: vscode.Uri
    ): { uri: vscode.Uri; line: number } | null {
        const workspaceRoot = this.getWorkspaceRoot(resource);
        if (!workspaceRoot) {
            return null;
        }

        const lockedVersion = this.getLockedVersion(key);

        // 单文件模式
        const promptsFilePath = path.join(workspaceRoot, 'prompts.yaml');
        if (fs.existsSync(promptsFilePath)) {
            let line = -1;
            if (lockedVersion) {
                line = this.findKeyLineInYaml(promptsFilePath, `${key}@${lockedVersion}`);
            }
            if (line < 0) {
                line = this.findKeyLineInYaml(promptsFilePath, key);
            }
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
            if (lockedVersion) {
                const lockedPath = path.join(promptDir, `${lockedVersion}.yaml`);
                if (fs.existsSync(lockedPath)) {
                    return {
                        uri: vscode.Uri.file(lockedPath),
                        line: 0,
                    };
                }
            }
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
            const keyPattern = new RegExp(`^${this.escapeRegExp(key)}\\s*:`);
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

    private escapeRegExp(text: string): string {
        return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    /**
     * 从单文件模式获取 prompt
     */
    private getFromSingleFile(filePath: string, key: string, version?: string): PromptData | null {
        try {
            const stat = fs.statSync(filePath);
            const mtime = stat.mtimeMs;
            const cache = getCache(path.dirname(filePath));

            // 使用缓存
            if (cache.singleFile && cache.singleFileMtime === mtime) {
                return selectPromptFromYaml(cache.singleFile, key, version);
            }

            // 重新加载
            const content = fs.readFileSync(filePath, 'utf-8');
            const prompts = yaml.load(content) as PromptsYaml;

            if (prompts && typeof prompts === 'object') {
                cache.singleFile = prompts;
                cache.singleFileMtime = mtime;
                return selectPromptFromYaml(prompts, key, version);
            }
        } catch (error) {
            console.error('[prompt-vcs] Failed to parse prompts.yaml:', error);
        }
        return null;
    }

    /**
     * 从多文件模式获取 prompt
     */
    private getFromMultiFile(workspaceRoot: string, key: string, version?: string): PromptData | null {
        const promptDir = path.join(workspaceRoot, 'prompts', key);
        if (!fs.existsSync(promptDir)) {
            return null;
        }

        if (version) {
            const versionPath = path.join(promptDir, `${version}.yaml`);
            if (fs.existsSync(versionPath)) {
                return this.readYamlFile(versionPath);
            }
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

    private getLockedVersion(promptId: string, resource?: vscode.Uri): string | null {
        const workspaceRoot = this.getWorkspaceRoot(resource);
        if (!workspaceRoot) {
            return null;
        }

        const lockfilePath = path.join(workspaceRoot, this.lockfileName);
        if (!fs.existsSync(lockfilePath)) {
            return null;
        }

        try {
            const stat = fs.statSync(lockfilePath);
            const mtime = stat.mtimeMs;
            const cache = getCache(workspaceRoot);

            if (cache.lockfile && cache.lockfileMtime === mtime) {
                return cache.lockfile[promptId] ?? null;
            }

            const raw = fs.readFileSync(lockfilePath, 'utf-8');
            const data = JSON.parse(raw) as Record<string, string>;
            cache.lockfile = data;
            cache.lockfileMtime = mtime;

            return data[promptId] ?? null;
        } catch {
            return null;
        }
    }

    /**
     * 在行文本中查找光标位置对应的 key
     */
    findKeyAtPosition(
        lineText: string,
        cursorPosition: number
    ): { key: string; startIndex: number; endIndex: number } | null {
        return findPromptCallAtPosition(lineText, cursorPosition);
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

            const promptData = this.dataProvider.getPromptData(keyInfo.key, document.uri);
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

            const location = this.dataProvider.getPromptLocation(keyInfo.key, document.uri);
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

            const promptIds = this.dataProvider.getAllPromptIds(document.uri);
            if (promptIds.length === 0) {
                return null;
            }

            return promptIds.map(id => {
                const item = new vscode.CompletionItem(id, vscode.CompletionItemKind.Value);
                item.detail = 'Prompt ID';

                // 获取 prompt 数据以显示描述
                const data = this.dataProvider.getPromptData(id, document.uri);
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
