// Выбор контроля времени (TimeControlPicker): подпись выбранного варианта, раскрытие списка по категориям, выбор
// варианта, блокировка при назначенной партии и ручная настройка минут и добавки с зажимом в допустимые пределы.

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
    it('закрытый список показывает выбранный вариант, клик по кнопке раскрывает его', () => {
        const props = setup();
        fireEvent.click(screen.getByRole('button'));
        expect(props.onToggleOpen).toHaveBeenCalledTimes(1);
        expect(screen.getAllByText(PRESET.label).length).toBeGreaterThan(0);
    });

    it('открытый список содержит все категории и отдаёт выбранный вариант', () => {
        const props = setup({isOpen: true});
        for (const g of TIME_CONTROLS) expect(screen.getAllByText(g.title).length).toBeGreaterThan(0);
        const other = ALL.find((o) => o.id !== PRESET.id && !o.isManual)!;
        fireEvent.click(screen.getAllByText(other.label)[0]);
        expect(props.onSelect).toHaveBeenCalledWith(other);
    });

    it('при назначенной партии кнопка недоступна', () => {
        setup({disabled: true});
        expect(screen.getByRole('button')).toBeDisabled();
    });

    it('ручной режим: поля и зажим значений в 1–240 минут и 0–180 секунд', () => {
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

    it('у готового варианта полей ручной настройки нет', () => {
        setup();
        expect(screen.queryAllByRole('spinbutton')).toHaveLength(0);
    });
});
