import { z } from 'zod';

export const kinds = ['flood', 'wildfire', 'volcano', 'earthquake', 'ice'] as const;
const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(s => {
  const d = new Date(`${s}T00:00:00Z`);
  return !Number.isNaN(+d) && d.toISOString().slice(0, 10) === s;
}, 'Invalid calendar date');
export const boundsSchema = z.tuple([z.number().finite(), z.number().min(-90).max(90), z.number().finite(), z.number().min(-90).max(90)])
  .refine(b => b[1] <= b[3], 'Invalid latitude interval');
export const eventSchema = z.object({
  id: z.string().regex(/^[a-z0-9-]+$/).max(100),
  title: z.string().min(1).max(300), country: z.string().min(1).max(100),
  countryCode: z.string().regex(/^[A-Z]{2}$/), region: z.string().max(100),
  aliases: z.array(z.string().max(100)).max(100), kind: z.enum(kinds), date: day,
  coordinates: z.tuple([z.number().min(-180).max(180), z.number().min(-90).max(90)]),
  description: z.string().max(10000), observations: z.array(day).optional(),
  source: z.string().url().refine(s => /^https?:/.test(s)).optional(),
  catalogVerified: z.boolean(), analysisAvailable: z.boolean(),
}).strict();
export type CatalogEvent = z.infer<typeof eventSchema>;
export const searchSchema = z.object({
  q: z.string().max(300).nullable().optional(), kinds: z.array(z.enum(kinds)).max(5).nullable().optional(),
  countries: z.array(z.string().max(100)).max(30).nullable().optional(),
  region: z.string().max(100).nullable().optional(),
  from: day.nullable().optional(), to: day.nullable().optional(),
  documentedOnly: z.boolean().nullable().optional(), analysisAvailable: z.boolean().nullable().optional(),
  bounds: boundsSchema.nullable().optional(), sort: z.enum(['newest', 'oldest', 'title']).optional(),
  limit: z.number().int().min(1).max(100).optional(),
}).strict().refine(s => !s.from || !s.to || s.from <= s.to, 'Start must precede end');
export type SearchInput = z.infer<typeof searchSchema>;
export const chatSchema = z.object({
  message: z.string().trim().min(1).max(4000),
  sessionId: z.string().uuid().optional(),
  context: z.object({
    selectedEventId: z.string().max(100).nullable(), bounds: boundsSchema.nullable(),
    filters: z.object({search:z.string().max(300), kinds:z.array(z.enum(kinds)).max(5),
      from:day, to:day, documentedOnly:z.boolean(), viewOnly:z.boolean()}).strict(),
    revision: z.number().int().nonnegative(),
    // Ordered IDs currently listed in the sidebar: what the user actually sees.
    listedIds: z.array(z.string().max(100)).max(100).optional(),
  }).strict(),
}).strict();
export type ChatInput = z.infer<typeof chatSchema>;
export type UIAction = {type:'show_results'; eventIds:string[]} | {type:'focus_event';eventId:string} |
  {type:'start_guide';eventId:string} | {type:'reset_map'};
export type OrbitReply = {sessionId:string; text:string; actions:UIAction[]; events:CatalogEvent[];
  sources:{title:string;url:string}[]; model:string; revision:number; toolsUsed:string[]};

export class ServiceError extends Error {
  status: number;
  code: string;
  constructor(status:number, code:string, message:string) {
    super(message); this.status=status; this.code=code;
  }
}
