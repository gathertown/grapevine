import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgKeyboardEnter = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8 15H16V9M8 15L10 17M8 15L10 13M21 19V5C21 3.895 20.105 3 19 3H13C11.895 3 11 3.895 11 5V9H5C3.895 9 3 9.895 3 11V19C3 20.105 3.895 21 5 21H19C20.105 21 21 20.105 21 19Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgKeyboardEnter);
export default Memo;