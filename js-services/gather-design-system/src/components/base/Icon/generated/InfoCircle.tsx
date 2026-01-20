import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgInfoCircle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 17V12H11M12 21C7.029 21 3 16.971 3 12C3 7.029 7.029 3 12 3C16.971 3 21 7.029 21 12C21 16.971 16.971 21 12 21ZM11.749 8C11.611 8 11.499 8.112 11.5 8.25C11.5 8.388 11.612 8.5 11.75 8.5C11.888 8.5 12 8.388 12 8.25C12 8.112 11.888 8 11.749 8Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M11.749 8C11.611 8 11.499 8.112 11.5 8.25C11.5 8.388 11.612 8.5 11.75 8.5C11.888 8.5 12 8.388 12 8.25C12 8.112 11.888 8 11.749 8" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgInfoCircle);
export default Memo;