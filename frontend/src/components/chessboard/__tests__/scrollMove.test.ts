// The move list scrolls by itself, the page does not: the current move is placed in the middle of the list window.

import {describe, expect, it, vi} from 'vitest';
import {centeredScrollTop, scrollMoveIntoList} from '../scrollMove';

const box = (top: number, height: number) => ({top, height, bottom: top + height, left: 0, right: 0, width: 0, x: 0, y: top, toJSON: () => ({})}) as DOMRect;

/** A list window 300 high at screen coordinate 200, content 2000, rows of 30. */
function listWith(scrollTop: number, moveScreenTop: number) {
    const list = document.createElement('div');
    const move = document.createElement('button');
    list.appendChild(move);
    Object.defineProperty(list, 'clientHeight', {value: 300});
    Object.defineProperty(list, 'scrollHeight', {value: 2000});
    list.scrollTop = scrollTop;
    list.getBoundingClientRect = () => box(200, 300);
    move.getBoundingClientRect = () => box(moveScreenTop, 30);
    return {list, move};
}

describe('centeredScrollTop', () => {
    it('places the row in the middle of the window', () => {
        expect(centeredScrollTop(900, 30, 300, 2000)).toBe(765);
    });

    it('at the start and at the end of the list it does not go beyond the edges', () => {
        expect(centeredScrollTop(30, 30, 300, 2000)).toBe(0);
        expect(centeredScrollTop(1970, 30, 300, 2000)).toBe(1700);
    });

    it('the list fits entirely in the window — no scrolling', () => {
        expect(centeredScrollTop(120, 30, 300, 240)).toBe(0);
    });
});

describe('scrollMoveIntoList', () => {
    it('scrolls the list to the move taking into account the scroll already made', () => {
        // The move is 400 px below the top of the list window, the list is already scrolled by 500 → the row is at 900 from the start of the content.
        const {list, move} = listWith(500, 600);
        scrollMoveIntoList(list, move);
        expect(list.scrollTop).toBe(765);
    });

    it('a move above the visible part — the list scrolls back', () => {
        const {list, move} = listWith(1000, 100);  // 100 px above the window: 900 from the start of the content
        scrollMoveIntoList(list, move);
        expect(list.scrollTop).toBe(765);
    });

    it('does not touch the page: neither scrollIntoView nor window scrolling', () => {
        const {list, move} = listWith(0, 900);
        const intoView = vi.fn();
        move.scrollIntoView = intoView;
        const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
        scrollMoveIntoList(list, move);
        expect(intoView).not.toHaveBeenCalled();
        expect(scrollTo).not.toHaveBeenCalled();
        scrollTo.mockRestore();
    });
});
