import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowUp = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 5V19M12 5L6.99902 10M12 5L17.001 10" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowUp);
export default Memo;