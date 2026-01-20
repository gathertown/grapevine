import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgPen = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.25 6.25006L16.0858 3.41428C16.8668 2.63323 18.1332 2.63323 18.9142 3.41428L20.5858 5.08585C21.3668 5.8669 21.3668 7.13323 20.5858 7.91428L17.75 10.7501M13.25 6.25006L3.33579 16.1643C2.96071 16.5394 2.75 17.0481 2.75 17.5785V21.2501H6.42157C6.95201 21.2501 7.46071 21.0394 7.83579 20.6643L17.75 10.7501M13.25 6.25006L17.75 10.7501" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgPen);
export default Memo;