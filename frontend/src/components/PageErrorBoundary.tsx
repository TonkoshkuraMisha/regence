// Page safety guard: a rendering error on one page does not take down the whole app: the header and menu stay,
// and in the page's place there is a message and "Refresh". It resets on navigation to another address (resetKey).
// Texts are the common.* catalog (i18n); the error is written to the browser console. Wraps the routes in App.tsx.

import {Component} from 'react';
import type {ErrorInfo, ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {useI18n} from '../i18n';
import {reportClientError} from '../services/clientErrors';
import {captureRenderError} from '../services/sentry';

/** Fallback view of a page: a message, a reload and a link to the home page. */
function Fallback() {
    const {t} = useI18n();
    return (
        <div className="w-full max-w-xl mx-auto p-6 flex flex-col gap-3 text-boxwood-light" role="alert" data-testid="page-error">
            <h1 className="text-xl font-bold text-amber-200">{t('common.pageError')}</h1>
            <p className="text-boxwood/85">{t('common.pageErrorHint')}</p>
            <div className="flex flex-wrap gap-3">
                <button type="button" onClick={() => window.location.reload()} className="px-4 py-2 rounded bg-amber-700 text-white font-bold">
                    {t('common.pageReload')}
                </button>
                <Link to="/" className="px-4 py-2 rounded bg-black/40 text-amber-200">{t('common.pageHome')}</Link>
            </div>
        </div>
    );
}

/** resetKey is the current page address: changing it clears the failure flag. */
interface Props {
    resetKey: string;
    children: ReactNode;
}

interface State {
    failed: boolean;
    key: string;
}

/**
 * Class component: catching rendering errors of descendants in React is possible only this way. The failure flag
 * (failed) is reset in getDerivedStateFromProps when resetKey changes.
 */
export class PageErrorBoundary extends Component<Props, State> {
    state: State = {failed: false, key: this.props.resetKey};

    static getDerivedStateFromError(): Partial<State> {
        return {failed: true};
    }

    static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
        return props.resetKey !== state.key ? {failed: false, key: props.resetKey} : null;
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error('page error', error, info.componentStack);
        captureRenderError(error, info.componentStack);
        void reportClientError('render', error.message, `${error.stack ?? ''}\n${info.componentStack ?? ''}`);
    }

    render() {
        return this.state.failed ? <Fallback/> : this.props.children;
    }
}
