import {lazy,Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';
import {EXPLORER_PATH} from './routes';
const Explorer=lazy(()=>import('./Explorer'));
const Landing=lazy(()=>import('./Landing'));
const exploring=window.location.pathname.replace(/\/$/,'')===EXPLORER_PATH;
createRoot(document.getElementById('root')!).render(<Suspense fallback={<div className="page-loading" role="status">Opening EarthSignal…</div>}>{exploring?<Explorer/>:<Landing/>}</Suspense>);
