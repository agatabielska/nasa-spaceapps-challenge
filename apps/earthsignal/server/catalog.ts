import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { eventSchema, searchSchema, type CatalogEvent, type SearchInput } from './contracts.ts';
import { inBounds, normalize } from '../src/domain.ts';

/** Bump when data/events.seed.json changes. */
const SEED_VERSION='3';

export class Catalog {
  db: DatabaseSync;
  constructor(filename:string, seed?:unknown) {
    if(filename !== ':memory:') mkdirSync(dirname(filename), {recursive:true});
    this.db = new DatabaseSync(filename);
    this.db.exec(`PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`);
    const version = this.db.prepare('PRAGMA user_version').get() as {user_version:number};
    if(version.user_version > 1) throw new Error('Database schema is newer than this application');
    if(version.user_version === 0) this.db.exec(`
      BEGIN;
      CREATE TABLE events(id TEXT PRIMARY KEY, kind TEXT NOT NULL, country TEXT NOT NULL,
        country_code TEXT NOT NULL, region TEXT NOT NULL, event_date TEXT NOT NULL,
        documented INTEGER NOT NULL CHECK(documented IN(0,1)), analysis_available INTEGER NOT NULL CHECK(analysis_available IN(0,1)),
        search_text TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)));
      CREATE INDEX events_category_date ON events(kind,event_date);
      CREATE INDEX events_place_date ON events(country_code,event_date);
      CREATE VIRTUAL TABLE events_fts USING fts5(id UNINDEXED, search_text, tokenize='unicode61 remove_diacritics 2');
      CREATE TRIGGER events_ai AFTER INSERT ON events BEGIN INSERT INTO events_fts(id,search_text) VALUES(new.id,new.search_text); END;
      CREATE TRIGGER events_au AFTER UPDATE ON events BEGIN DELETE FROM events_fts WHERE id=old.id; INSERT INTO events_fts(id,search_text) VALUES(new.id,new.search_text); END;
      CREATE TRIGGER events_ad AFTER DELETE ON events BEGIN DELETE FROM events_fts WHERE id=old.id; END;
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      PRAGMA user_version=1;
      COMMIT;
    `);
    // The bundled seed is re-imported (upsert) whenever its version changes, so an existing local database
    // picks up new and corrected catalog entries without a manual `npm run db:import`.
    const seeded=this.db.prepare("SELECT value FROM metadata WHERE key='seeded'").get() as {value:string}|undefined;
    if(seed && seeded?.value!==SEED_VERSION) {
      this.import(seed);
      this.db.prepare("INSERT INTO metadata(key,value) VALUES('seeded',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").run(SEED_VERSION);
    }
  }
  import(input:unknown) {
    if(!Array.isArray(input)) throw new Error('Import must contain an array');
    const records = input.map(e=>eventSchema.parse(e));
    if(new Set(records.map(e=>e.id)).size!==records.length) throw new Error('Duplicate IDs in import');
    const stmt=this.db.prepare(`INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
      kind=excluded.kind,country=excluded.country,country_code=excluded.country_code,region=excluded.region,
      event_date=excluded.event_date,documented=excluded.documented,analysis_available=excluded.analysis_available,
      search_text=excluded.search_text,payload=excluded.payload`);
    this.db.exec('BEGIN');
    try {
      for(const e of records) stmt.run(e.id,e.kind,e.country,e.countryCode,e.region,e.date,
        +e.catalogVerified,+e.analysisAvailable,normalize([e.title,e.description,e.country,e.region,...e.aliases].join(' ')),JSON.stringify(e));
      this.db.exec('COMMIT');
    } catch(e) {this.db.exec('ROLLBACK');throw e;}
    return records.length;
  }
  get(id:string):CatalogEvent|null {
    const row=this.db.prepare('SELECT payload FROM events WHERE id=?').get(id) as {payload:string}|undefined;
    return row?eventSchema.parse(JSON.parse(row.payload)):null;
  }
  search(input:SearchInput={}) {
    const s=searchSchema.parse(input), where:string[]=[], args:(string|number)[]=[];
    if(s.kinds) {if(!s.kinds.length)return {events:[],total:0};where.push(`kind IN (${s.kinds.map(()=>'?').join(',')})`);args.push(...s.kinds);}
    if(s.countries) {
      if(!s.countries.length)return {events:[],total:0};
      where.push(`(${s.countries.map(()=>'(lower(country)=? OR country_code=?)').join(' OR ')})`);
      for(const c of s.countries)args.push(c.toLowerCase(),c.toUpperCase());
    }
    if(s.region) {where.push('lower(region)=?');args.push(s.region.toLowerCase());}
    if(s.from){where.push('event_date>=?');args.push(s.from);}
    if(s.to){where.push('event_date<=?');args.push(s.to);}
    if(s.documentedOnly){where.push('documented=1');}
    if(s.analysisAvailable!==undefined&&s.analysisAvailable!==null){where.push('analysis_available=?');args.push(+s.analysisAvailable);}
    const tokens=normalize(s.q??'').match(/[\p{L}\p{N}]+/gu)?.slice(0,20);
    if(tokens?.length){where.push('id IN (SELECT id FROM events_fts WHERE events_fts MATCH ?)');args.push(tokens.map(t=>'"'+t+'"*').join(' AND '));}
    const sort={newest:'event_date DESC,id',oldest:'event_date ASC,id',title:'country,title'};
    // title is in the JSON payload; order only uses fixed, trusted expressions.
    const order=s.sort==='title'?"json_extract(payload,'$.title'),id":sort[s.sort??'newest'];
    const rows=this.db.prepare('SELECT payload FROM events'+(where.length?' WHERE '+where.join(' AND '):'')+' ORDER BY '+order).all(...args) as {payload:string}[];
    const matched=rows.map(r=>JSON.parse(r.payload) as CatalogEvent).filter(e=>inBounds(e.coordinates,s.bounds??null));
    return {events:matched.slice(0,s.limit??100),total:matched.length};
  }
  facets(){return this.db.prepare('SELECT DISTINCT country,country_code AS countryCode,region FROM events ORDER BY country').all();}
  close(){this.db.close();}
}
export function readSeed(){return JSON.parse(readFileSync(new URL('../data/events.seed.json',import.meta.url),'utf8'));}
