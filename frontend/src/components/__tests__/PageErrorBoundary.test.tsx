// The page error boundary: a render error shows a message instead of the page, navigating to another address resets it.

import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it, vi} from 'vitest';
import {PageErrorBoundary} from '../PageErrorBoundary';

function Broken({fail}: { fail: boolean }) {
    if (fail) throw new Error('boom');
    return <p data-testid="page-ok">ok</p>;
}

describe('page error boundary', () => {
    it('a message instead of the failed page and a reset on a new address', () => {
        const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
        const view = render(<MemoryRouter><PageErrorBoundary resetKey="/a"><Broken fail/></PageErrorBoundary></MemoryRouter>);
        expect(screen.getByTestId('page-error')).toHaveTextContent('Something went wrong on this page');
        view.rerender(<MemoryRouter><PageErrorBoundary resetKey="/b"><Broken fail={false}/></PageErrorBoundary></MemoryRouter>);
        expect(screen.getByTestId('page-ok')).toBeInTheDocument();
        spy.mockRestore();
    });
});
