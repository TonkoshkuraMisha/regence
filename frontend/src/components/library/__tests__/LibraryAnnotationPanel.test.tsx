// Library game annotation (task 27.4): the text for the current move, moving between comments, the status label.

import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {LibraryAnnotationPanel} from '../LibraryAnnotationPanel';
import type {LibraryAnnotation} from '../../../services/library';

const ANNOTATION: LibraryAnnotation = {
    status: 'auto', version: 1, evals: [],
    comments: {
        '3': {comment: [{key: 'coach.verdict.blunder.v1', params: {move: 'Nc6'}}]},
        '6': {comment: [{key: 'coach.verdict.inaccuracy.v1', params: {move: 'Nf6'}}]},
        '9': {comment: [{key: 'coach.no.such.key', params: {}}]},  // an unknown key — is not counted
    },
};

describe('library game annotation', () => {
    it('a comment on a move, the draft label and moving to the next one', () => {
        const onSelect = vi.fn();
        const view = render(<LibraryAnnotationPanel annotation={ANNOTATION} viewIndex={3} onSelect={onSelect}/>);
        expect(screen.getByTestId('library-annotation')).toHaveTextContent('draft, assembled automatically · 2 comments');
        expect(screen.getByTestId('library-annotation-text')).toHaveTextContent('Nc6');
        expect(screen.getByTestId('library-annotation-prev')).toBeDisabled();
        fireEvent.click(screen.getByTestId('library-annotation-next'));
        expect(onSelect).toHaveBeenCalledWith(6);
        view.rerender(<LibraryAnnotationPanel annotation={ANNOTATION} viewIndex={4} onSelect={onSelect}/>);
        expect(screen.getByTestId('library-annotation-text')).toHaveTextContent('No comment on this move.');
    });

    it('without understandable comments there is no panel', () => {
        const empty: LibraryAnnotation = {...ANNOTATION, comments: {'9': ANNOTATION.comments['9']}};
        const {container} = render(<LibraryAnnotationPanel annotation={empty} viewIndex={0} onSelect={vi.fn()}/>);
        expect(container).toBeEmptyDOMElement();
    });
});
