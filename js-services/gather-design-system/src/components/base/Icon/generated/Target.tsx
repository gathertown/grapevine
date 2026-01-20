import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgTarget = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" xmlnsXlink="http://www.w3.org/1999/xlink" {...props}><g strokeLinecap="round" strokeWidth={1.5} stroke="currentColor" fill="none" strokeLinejoin="round"><path d="M20.053,12.474c0,4.709 -3.817,8.526 -8.526,8.526c-4.709,0 -8.527,-3.817 -8.527,-8.526c0,-4.709 3.817,-8.526 8.526,-8.526" /><path d="M16.263,12.474c0,2.616 -2.121,4.737 -4.737,4.737c-2.616,0 -4.737,-2.121 -4.737,-4.737c0,-2.616 2.121,-4.737 4.737,-4.737" /><path d="M18.158,3l-2.842,2.842v2.842h2.842l2.842,-2.842l-1.895,-0.947Z" /><path d="M15.32,8.68l-3.79,3.79" /></g><path fill="none" d="M0,0h24v24h-24Z" /></svg>;
const Memo = memo(SvgTarget);
export default Memo;