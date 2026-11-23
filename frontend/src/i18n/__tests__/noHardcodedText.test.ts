// --- FILE: frontend/src/i18n/__tests__/noHardcodedText.test.ts ---
// A guard for the rule "all text lives in the catalogs": it parses the sources with the TypeScript tokenizer and fails on any
// Cyrillic in strings, templates and JSX text outside the catalogs. Comments are skipped — they are for developers
// and are written in English. A new interface string written straight into a component will fail this test.

import {readdirSync, readFileSync} from 'node:fs';
import {join, relative, sep} from 'node:path';
import ts from 'typescript';
import {describe, expect, it} from 'vitest';

const SRC = join(__dirname, '..', '..');
const CYRILLIC = /[\u0400-\u04FF]/;

// The message catalogs are the only place for text; tests and test utilities are written in English.
const ALLOWED = [`i18n${sep}messages${sep}`, `${sep}__tests__${sep}`, `test${sep}`];

function sourceFiles(dir: string): string[] {
    return readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) return sourceFiles(path);
        return /\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.d.ts') ? [path] : [];
    });
}

const TEXT_TOKENS = new Set([
    ts.SyntaxKind.StringLiteral,
    ts.SyntaxKind.NoSubstitutionTemplateLiteral,
    ts.SyntaxKind.TemplateHead,
    ts.SyntaxKind.TemplateMiddle,
    ts.SyntaxKind.TemplateTail,
    ts.SyntaxKind.JsxText,
]);

/** Strings with Cyrillic in code (not in comments): "file:line: text". */
function hardcodedText(file: string): string[] {
    const text = readFileSync(file, 'utf-8');
    const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true,
        file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const found: string[] = [];
    const visit = (node: ts.Node) => {
        if (TEXT_TOKENS.has(node.kind) && CYRILLIC.test(node.getText(source))) {
            const {line} = source.getLineAndCharacterOfPosition(node.getStart(source));
            found.push(`${relative(SRC, file)}:${line + 1}: ${node.getText(source).trim().slice(0, 90)}`);
        }
        ts.forEachChild(node, visit);
    };
    visit(source);
    return found;
}

describe('interface text — only in the catalogs', () => {
    it('components, hooks, services and configs have no Cyrillic outside comments', () => {
        const offenders = sourceFiles(SRC)
            .filter((file) => !ALLOWED.some((allowed) => file.includes(allowed)))
            .flatMap(hardcodedText);
        expect(offenders, `\n${offenders.join('\n')}`).toEqual([]);
    });

    it('the guard really finds text in a string, a template and JSX', () => {
        // The Cyrillic sample is built from code points so that this file itself contains no Cyrillic letters.
        const sample = '\u0442\u0435\u043A\u0441\u0442';
        const probe = join(SRC, 'i18n', '__tests__', 'probe.tsx');
        const source = ts.createSourceFile(probe, [
            `// ${sample} in a comment does not count`,
            `const a = '${sample}';`,
            `const b = \`${sample} \${a}\`;`,
            `const c = <p>${sample}</p>;`,
        ].join('\n'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
        const kinds: ts.SyntaxKind[] = [];
        const visit = (node: ts.Node) => {
            if (TEXT_TOKENS.has(node.kind) && CYRILLIC.test(node.getText(source))) kinds.push(node.kind);
            ts.forEachChild(node, visit);
        };
        visit(source);
        expect(kinds).toEqual([ts.SyntaxKind.StringLiteral, ts.SyntaxKind.TemplateHead, ts.SyntaxKind.JsxText]);
    });
});
