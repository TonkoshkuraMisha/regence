// Time control picker (TimeControlPicker): the label of the chosen option, expanding the list by categories, choosing
// an option, blocking when a game is assigned and manual setting of minutes and increment clamped to the allowed limits.

import {createRef} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {TimeControlPicker} from '../TimeControlPicker';
import type {TimeControlPickerProps} from '../TimeControlPicker';
import {TIME_CONTROLS} from '../../../config/timeControls';

const ALL = TIME_CONTROLS.flatMap((g) => g.options);
const PRESET = ALL.find((o) => !o.isManual)!;
const MANUAL = ALL.find((o) => o.isManual)!;

function setup(over: Partial<TimeControlPickerProps> = {}) {
    const props: TimeControlPickerProps = {
        selectedTimeControl: PRESET, manualBaseMinutes: 7, manualIncSeconds: 4,
        onManualBaseMinutesChange: vi.fn(), onManualIncSecondsChange: vi.fn(),
        isOpen: false, onToggleOpen: vi.fn(), onSelect: vi.fn(), disabled: false,
        dropdownRef: createRef<HTMLDivElement>(), ...over,
    };
    render(<TimeControlPicker {...props}/>);
    return props;
}

describe('TimeControlPicker', () => {
    it('the closed list shows the chosen option, a click on the button expands it', () => {
        const props = setup();
        fireEvent.click(screen.getByRole('button'));
        expect(props.onToggleOpen).toHaveBeenCalledTimes(1);
        expect(screen.getAllByText(PRESET.label).length).toBeGreaterThan(0);
    });

    it('the open list contains all categories and returns the chosen option', () => {
        const props = setup({isOpen: true});
        for (const g of TIME_CONTROLS) expect(screen.getAllByText(g.title).length).toBeGreaterThan(0);
        const other = ALL.find((o) => o.id !== PRESET.id && !o.isManual)!;
        fireEvent.click(screen.getAllByText(other.label)[0]);
        expect(props.onSelect).toHaveBeenCalledWith(other);
    });

    it('with an assigned game the button is unavailable', () => {
        setup({disabled: true});
        expect(screen.getByRole('button')).toBeDisabled();
    });

    it('manual mode: fields and clamping of values to 1–240 minutes and 0–180 seconds', () => {
        const props = setup({selectedTimeControl: MANUAL, isOpen: true});
        const [base, inc] = screen.getAllByRole('spinbutton');
        expect(base).toHaveValue(7);
        expect(inc).toHaveValue(4);
        fireEvent.change(base, {target: {value: '999'}});
        expect(props.onManualBaseMinutesChange).toHaveBeenLastCalledWith(240);
        fireEvent.change(base, {target: {value: '0'}});
        expect(props.onManualBaseMinutesChange).toHaveBeenLastCalledWith(1);
        fireEvent.change(inc, {target: {value: '500'}});
        expect(props.onManualIncSecondsChange).toHaveBeenLastCalledWith(180);
        fireEvent.change(inc, {target: {value: '-5'}});
        expect(props.onManualIncSecondsChange).toHaveBeenLastCalledWith(0);
    });

    it('a ready-made option has no manual setting fields', () => {
        setup();
        expect(screen.queryAllByRole('spinbutton')).toHaveLength(0);
    });
});
