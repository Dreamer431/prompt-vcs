import assert from 'node:assert/strict';
import test from 'node:test';

import {
    findPromptCallAtPosition,
    selectPromptFromYaml,
} from '../promptUtils';

test('findPromptCallAtPosition resolves the prompt under the cursor', () => {
    const line = 'value = p("user_greeting", name=user)';
    const match = findPromptCallAtPosition(line, line.indexOf('user_greeting'));

    assert.deepEqual(match, {
        key: 'user_greeting',
        startIndex: line.indexOf('p('),
        endIndex: line.indexOf('",') + 1,
    });
});

test('selectPromptFromYaml resolves nested locked versions', () => {
    const prompt = selectPromptFromYaml(
        {
            greeting: {
                template: 'Base',
                versions: {
                    v2: { template: 'Version two', description: 'formal' },
                },
            },
        },
        'greeting',
        'v2'
    );

    assert.deepEqual(prompt, {
        template: 'Version two',
        description: 'formal',
    });
});

test('selectPromptFromYaml resolves flat locked versions', () => {
    const prompt = selectPromptFromYaml(
        {
            greeting: { template: 'Base' },
            'greeting@v2': { template: 'Version two' },
        },
        'greeting',
        'v2'
    );

    assert.deepEqual(prompt, { template: 'Version two', description: undefined });
});
