import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgVideoClip = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M4 12H8M4 12V8M4 12V16M8 12H16M8 12V16M8 12V8M4 8V7C4 5.34315 5.34315 4 7 4H8M4 8H8M4 16V17C4 18.6569 5.34315 20 7 20H8M4 16H8M16 12H20M16 12V16.4444M16 12V8M8 16V20M8 8V4M20 12V8M20 12V16.4444M16 16.4444V20M16 16.4444H20M16 8V4M16 8H20M20 8V7C20 5.34315 18.6569 4 17 4H16M20 16.4444V17C20 18.6569 18.6569 20 17 20H16M16 20H8M16 4H8" stroke="currentColor" strokeWidth={1.5} strokeLinecap="square" /></svg>;
const Memo = memo(SvgVideoClip);
export default Memo;