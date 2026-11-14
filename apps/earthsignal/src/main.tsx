import {lazy,Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';
const Explorer=lazy(()=>import('./Explorer'));
const Landing=lazy(()=>import('./Landing'));
const exploring=window.location.pathname.replace(/\/$/,'')==='/explore';
createRoot(document.getElementById('root')!).render(<Suspense fallback={<div className="page-loading" role="status">Opening EarthSignal…</div>}>{exploring?<Explorer/>:<Landing/>}</Suspense>);
