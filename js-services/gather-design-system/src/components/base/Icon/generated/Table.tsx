import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgTable = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M2.75 18.25V7.75C2.75 6.64543 3.64543 5.75 4.75 5.75H11.25M11.25 5.75H19.25C20.3546 5.75 21.25 6.64543 21.25 7.75V18.25H11.25V5.75ZM14.75 9.75V10.75" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgTable);
export default Memo;