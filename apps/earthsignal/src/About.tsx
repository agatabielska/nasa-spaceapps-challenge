import {useEffect} from 'react';
import {ArrowLeft,ArrowUpRight,Camera} from 'lucide-react';
import {EXPLORER_PATH} from './routes';
import {TEAM,TEAM_NAME,TEAM_PHOTO} from './team';
import './about.css';

// /about: who made EarthSignal. The team photo goes in the frame once TEAM_PHOTO (src/team.ts) is set.
export default function About(){
  useEffect(()=>{document.title='EarthSignal — About us';},[]);
  const [first,...rest]=TEAM_NAME.split(' ');
  return <div className="about">
    <header className="ab-nav"><a href="/"><ArrowLeft size={16} aria-hidden="true"/>Back to the journey</a><a href={EXPLORER_PATH}>Open the app <ArrowUpRight size={16} aria-hidden="true"/></a></header>
    <main>
      <p className="ab-kicker">NASA Space Apps Challenge 2026 · EarthSignal</p>
      <h1>Team <em>{first}</em> {rest.join(' ')}</h1>
      <div className="ab-grid">
        <figure className="ab-photo">{TEAM_PHOTO?<img src={TEAM_PHOTO} alt={`Team ${TEAM_NAME}`}/>:<div><Camera size={34} aria-hidden="true"/><span>Team photo coming soon</span></div>}</figure>
        <ul>{TEAM.map(name=><li key={name}>{name}</li>)}</ul>
      </div>
    </main>
  </div>;
}
