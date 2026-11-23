// The "Privacy" page (task 23.1): all five sections and the title come from the i18n catalogue.
import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {PrivacyPage} from '../PrivacyPage';

describe('PrivacyPage', () => {
    it('shows the title and five sections', () => {
        render(<PrivacyPage/>);
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Privacy');
        expect(screen.getAllByRole('heading', {level: 2})).toHaveLength(5);
        expect(screen.getByTestId('privacy-page')).toHaveTextContent('90 days');
    });
});
