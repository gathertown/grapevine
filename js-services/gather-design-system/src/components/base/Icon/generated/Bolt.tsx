import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgBolt = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.823 11.575L12.812 20.258C12.261 21.053 11.014 20.664 11.014 19.696V13.973H5.98901C5.19301 13.973 4.72401 13.079 5.17801 12.424L11.189 3.74104C11.74 2.94604 12.987 3.33504 12.987 4.30304V10.026H18.012C18.807 10.026 19.276 10.92 18.823 11.575Z" stroke="currentColor" strokeWidth={1.5383} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgBolt);
export default Memo;