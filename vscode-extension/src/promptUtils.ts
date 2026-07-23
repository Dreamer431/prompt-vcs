export interface PromptData {
    template: string;
    description?: string;
}

export interface PromptVersionedData extends PromptData {
    versions?: Record<string, string | PromptData>;
}

export type PromptsYaml = Record<string, string | PromptVersionedData>;

export interface PromptCallMatch {
    key: string;
    startIndex: number;
    endIndex: number;
}

export function findPromptCallAtPosition(
    lineText: string,
    cursorPosition: number
): PromptCallMatch | null {
    const pattern = /p\s*\(\s*['"]([^'"]+)['"]/g;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(lineText)) !== null) {
        const startIndex = match.index;
        const endIndex = match.index + match[0].length;
        if (cursorPosition >= startIndex && cursorPosition <= endIndex) {
            return {
                key: match[1],
                startIndex,
                endIndex,
            };
        }
    }
    return null;
}

export function parsePromptValue(value: unknown): PromptData | null {
    if (typeof value === 'string') {
        return { template: value };
    }
    if (value && typeof value === 'object') {
        const prompt = value as PromptData;
        if (typeof prompt.template === 'string') {
            return {
                template: prompt.template,
                description: prompt.description,
            };
        }
    }
    return null;
}

export function selectPromptFromYaml(
    prompts: PromptsYaml,
    key: string,
    version?: string
): PromptData | null {
    if (version) {
        const flatVersion = prompts[`${key}@${version}`];
        if (flatVersion !== undefined) {
            return parsePromptValue(flatVersion);
        }

        const base = prompts[key];
        if (base && typeof base === 'object' && 'versions' in base) {
            const versionValue = base.versions?.[version];
            if (versionValue !== undefined) {
                return parsePromptValue(versionValue);
            }
        }
    }

    return parsePromptValue(prompts[key]);
}
