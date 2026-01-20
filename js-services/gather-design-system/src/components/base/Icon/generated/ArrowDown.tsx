import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowDown = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 19V5M12 19L17.001 13.999M12 19L6.99902 13.999" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowDown);
export default Memo;