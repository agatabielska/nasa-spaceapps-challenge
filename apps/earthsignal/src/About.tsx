import {useEffect} from 'react';
import {ArrowLeft,ArrowUpRight} from 'lucide-react';
import {EXPLORER_PATH} from './routes';
import {TEAM,TEAM_NAME,TEAM_PHOTO,portrait} from './team';
import './about.css';

// /about: who made EarthSignal, with a portrait of each member. A group photo appears above them once
// TEAM_PHOTO (src/team.ts) is set.
export default function About(){
  useEffect(()=>{document.title='EarthSignal — About us';},[]);
  const [first,...rest]=TEAM_NAME.split(' ');
  return <div className="about">
    <header className="ab-nav"><a href="/"><ArrowLeft size={16} aria-hidden="true"/>Back to the journey</a><a href={EXPLORER_PATH}><span className="ab-hide-sm">Open the </span>app <ArrowUpRight size={16} aria-hidden="true"/></a></header>
    <main>
      <p className="ab-kicker">NASA Space Apps Challenge 2026 · EarthSignal</p>
      <h1>Team <em>{first}</em> {rest.join(' ')}</h1>
      {TEAM_PHOTO&&<figure className="ab-photo"><img src={TEAM_PHOTO} alt={`Team ${TEAM_NAME}`}/></figure>}
      <ul className="ab-team">{TEAM.map(name=><li key={name}><img src={portrait(name)} alt=""/><span>{name}</span></li>)}</ul>
    </main>
  </div>;
}
