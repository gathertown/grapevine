import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgExclamationCircle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 12.5V7.5M12 3C16.971 3 21 7.029 21 12C21 16.971 16.971 21 12 21C7.029 21 3 16.971 3 12C3 7.029 7.029 3 12 3Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M11.999 16C11.861 16 11.749 16.112 11.75 16.25C11.75 16.388 11.862 16.5 12 16.5C12.138 16.5 12.25 16.388 12.25 16.25C12.25 16.112 12.138 16 11.999 16" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgExclamationCircle);
export default Memo;