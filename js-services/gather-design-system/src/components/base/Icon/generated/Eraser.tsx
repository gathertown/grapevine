import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgEraser = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8.08988 9.38997L14.2199 15.52M20.9999 19.98H8.92988M7.52688 19.977H8.93388C9.46388 19.977 9.97288 19.766 10.3479 19.391L19.0719 10.667C19.8529 9.88597 19.8529 8.61997 19.0719 7.83897L15.7729 4.53997C14.9919 3.75897 13.7259 3.75897 12.9449 4.53997L3.51788 13.967C2.73688 14.748 2.73688 16.014 3.51788 16.795L6.11388 19.391C6.48788 19.766 6.99588 19.977 7.52688 19.977Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgEraser);
export default Memo;