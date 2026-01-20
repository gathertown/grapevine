import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCircleSlash = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.364 5.636L5.636 18.364M12 3C7.029 3 3 7.029 3 12C3 16.971 7.029 21 12 21C16.971 21 21 16.971 21 12C21 7.029 16.971 3 12 3Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCircleSlash);
export default Memo;