import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgOption = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M3.75 4.75H6.81924C7.54768 4.75 8.21851 5.14604 8.5704 5.78385L15.4296 18.2162C15.7815 18.854 16.4523 19.25 17.1808 19.25H20.25M15.75 4.75H20.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgOption);
export default Memo;