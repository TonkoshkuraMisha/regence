// The "Terms of use" page (tasks 17.5 / 23.1): the title and seven sections come from the i18n catalogue.
import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {TermsPage} from '../TermsPage';

describe('TermsPage', () => {
    it('shows the title and seven sections', () => {
        render(<TermsPage/>);
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Terms of use');
        expect(screen.getAllByRole('heading', {level: 2})).toHaveLength(7);
        expect(screen.getByTestId('terms-page')).toHaveTextContent('16');
    });
});
