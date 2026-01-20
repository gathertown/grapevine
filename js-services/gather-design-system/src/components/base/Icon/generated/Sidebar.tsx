import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSidebar = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9 20V5M6 20H18C19.6569 20 21 18.8807 21 17.5V7.5C21 6.11929 19.6569 5 18 5H6C4.34315 5 3 6.11929 3 7.5V17.5C3 18.8807 4.34315 20 6 20Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSidebar);
export default Memo;