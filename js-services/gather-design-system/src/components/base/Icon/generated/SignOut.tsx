import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSignOut = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.86005 12H20.0001M20.0001 12L16.0001 16M20.0001 12L16.0001 8M10.8641 19.981L6.69605 20C5.50105 20.006 4.52905 19.048 4.52905 17.865V6.135C4.52905 4.956 5.49405 4 6.68605 4H11.0001" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSignOut);
export default Memo;