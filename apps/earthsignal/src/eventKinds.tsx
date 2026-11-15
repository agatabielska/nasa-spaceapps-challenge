import {Activity,Flame,Mountain,Snowflake,Waves,type LucideIcon} from 'lucide-react';
import type {Kind} from './domain';

// How each event type looks in the dashboard: the same lucide icons and colours as the landing page
// (cases.ts), plus Waves for floods. domain.ts keeps the data side (keys and labels) free of React.
export const kindStyle:Record<Kind,{Icon:LucideIcon;color:string}>={
  flood:{Icon:Waves,color:'#6ea8ff'},
  wildfire:{Icon:Flame,color:'#ff9a3c'},
  volcano:{Icon:Mountain,color:'#ff6b6b'},
  earthquake:{Icon:Activity,color:'#ffd84d'},
  ice:{Icon:Snowflake,color:'#9be7ff'},
};

// An event type's icon, decorative: the type's name is always shown or announced next to it.
export function KindIcon({kind,size=18}:{kind:Kind;size?:number}){
  const {Icon}=kindStyle[kind];
  return <Icon size={size} strokeWidth={2.2} aria-hidden="true" focusable="false"/>;
}
