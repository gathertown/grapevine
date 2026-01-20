import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChevronRight = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9 20L17 12L9 4" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgChevronRight);
export default Memo;