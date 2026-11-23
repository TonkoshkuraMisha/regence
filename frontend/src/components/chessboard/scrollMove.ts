// --- FILE: frontend/src/components/chessboard/scrollMove.ts ---
// The move list is a separate window with its own scrolling, and the current move is kept in its middle (this is how analysis boards
// on chess sites work). Only the list itself scrolls: Element.scrollIntoView also moves the page,
// and when paging through a game with arrows the board "jumped" up and down following the move.

/** Where to scroll a list of height viewHeight so that a row (itemTop from the start of the content, itemHeight) ends up in the middle. */
export function centeredScrollTop(itemTop: number, itemHeight: number, viewHeight: number, contentHeight: number): number {
    const target = itemTop - (viewHeight - itemHeight) / 2;
    return Math.round(Math.max(0, Math.min(target, Math.max(0, contentHeight - viewHeight))));
}

/** Puts the move in the middle of the list without touching the page scroll. */
export function scrollMoveIntoList(list: HTMLElement, move: HTMLElement): void {
    const listBox = list.getBoundingClientRect();
    const moveBox = move.getBoundingClientRect();
    const itemTop = moveBox.top - listBox.top + list.scrollTop;
    list.scrollTop = centeredScrollTop(itemTop, moveBox.height, list.clientHeight, list.scrollHeight);
}
