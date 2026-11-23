// Shared design components (owner plan 18.11): button kinds, a link card and a button card, progress with a role,
// tabs with keyboard arrows, the page frame; the /design showcase is drawn in both languages.

import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it, vi} from 'vitest';
import {Badge, Button, ButtonLink, buttonClasses, Card, EmptyState, Page, PageHeader, ProgressBar, SegmentedControl} from '..';
import {DesignGallery} from '../../DesignGallery';
import {setLanguage} from '../../../i18n';

describe('buttons', () => {
    it('the kind and size give their own classes; a link looks the same', () => {
        expect(buttonClasses('primary', 'lg')).toContain('bg-amber-700');
        expect(buttonClasses('primary', 'lg')).toContain('px-5');
        expect(buttonClasses('danger')).toContain('bg-rose-900/70');
        render(<MemoryRouter><Button variant="primary">A</Button><ButtonLink to="/x" variant="primary">B</ButtonLink></MemoryRouter>);
        expect(screen.getByRole('button', {name: 'A'}).className).toBe(screen.getByRole('link', {name: 'B'}).className);
        expect(screen.getByRole('button', {name: 'A'})).toHaveAttribute('type', 'button');
    });
});

describe('cards', () => {
    it('with to — a link, with onClick — a button, otherwise — a block', () => {
        const onClick = vi.fn();
        render(<MemoryRouter>
            <Card to="/learn" title="link" testId="c1"/>
            <Card onClick={onClick} title="button" testId="c2" badge={<Badge tone="success">ok</Badge>}/>
            <Card title="plain" testId="c3" footer={<span>foot</span>}/>
        </MemoryRouter>);
        expect(screen.getByTestId('c1').tagName).toBe('A');
        expect(screen.getByTestId('c1')).toHaveAttribute('href', '/learn');
        fireEvent.click(screen.getByTestId('c2'));
        expect(onClick).toHaveBeenCalled();
        expect(screen.getByTestId('c2')).toHaveTextContent('ok');
        expect(screen.getByTestId('c3').tagName).toBe('DIV');
        expect(screen.getByTestId('c3')).toHaveTextContent('foot');
    });
});

describe('indicators and frame', () => {
    it('progress reports the value to screen readers, an empty state — with an action, the page heading — h1', () => {
        render(<MemoryRouter>
            <Page testId="page"><PageHeader title="Title" description="desc" actions={<Button>act</Button>}/></Page>
            <ProgressBar value={3} max={10} label="Progress"/>
            <EmptyState title="Empty" action={<Button>go</Button>}/>
        </MemoryRouter>);
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Title');
        const bar = screen.getByRole('progressbar', {name: 'Progress'});
        expect(bar).toHaveAttribute('aria-valuenow', '3');
        expect(screen.getByText('3 / 10')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'go'})).toBeInTheDocument();
    });
});

describe('tabs', () => {
    it('a click and keyboard arrows change the selection', () => {
        const onChange = vi.fn();
        render(<SegmentedControl label="modes" value="a" onChange={onChange} testIdPrefix="t"
                                 options={[{id: 'a', label: 'A'}, {id: 'b', label: 'B'}, {id: 'c', label: 'C'}]}/>);
        expect(screen.getByRole('tablist', {name: 'modes'})).toBeInTheDocument();
        expect(screen.getByTestId('t-a')).toHaveAttribute('aria-selected', 'true');
        fireEvent.click(screen.getByTestId('t-b'));
        expect(onChange).toHaveBeenLastCalledWith('b');
        fireEvent.keyDown(screen.getByTestId('t-a'), {key: 'ArrowLeft'});
        expect(onChange).toHaveBeenLastCalledWith('c');
    });
});

describe('/design showcase', () => {
    it.each(['uk', 'en'] as const)('is drawn in language %s without keys instead of text', (language) => {
        setLanguage(language, {persist: false});
        render(<MemoryRouter><DesignGallery/></MemoryRouter>);
        const page = screen.getByTestId('design-gallery');
        expect(page.textContent).not.toMatch(/design\.\w+/);
        expect(screen.getAllByRole('progressbar').length).toBeGreaterThan(2);
        setLanguage('en', {persist: false});
    });
});
