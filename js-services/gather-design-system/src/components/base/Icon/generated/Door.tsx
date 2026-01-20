import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgDoor = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M2.75 21.25H21.25M4.75 21.25V4.75C4.75 3.64543 5.64543 2.75 6.75 2.75H17.25C18.3546 2.75 19.25 3.64543 19.25 4.75V21.25M7.75 12.25H8.75" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgDoor);
export default Memo;