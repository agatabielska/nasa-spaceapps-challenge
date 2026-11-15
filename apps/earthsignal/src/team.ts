// The team, alphabetically by surname: shown on the landing page's start screen and footer, and on /about.
export const TEAM_NAME='Blue Trust';
export const TEAM=['Agata Bielska','Michał Leszczyński','Maria Musiał','Oliwier Necelman','Jakub Radziejewski','Martyna Stasiak'];
// Team photo for /about: put the file in public/media/ and set its path here (null shows only the portraits).
export const TEAM_PHOTO:string|null=null;
// Portraits in public/media/team/, by name; shown on /about and on the title of /show2.
const FILE:Record<string,string>={'Agata Bielska':'agata','Michał Leszczyński':'michal','Maria Musiał':'marysia','Oliwier Necelman':'oliwier','Jakub Radziejewski':'kuba','Martyna Stasiak':'martyna'};
export const portrait=(name:string)=>`/media/team/${FILE[name]}.webp`;
