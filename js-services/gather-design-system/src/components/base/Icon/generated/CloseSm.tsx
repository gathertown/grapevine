import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCloseSm = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8 8L16 16M16 8L8 16" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCloseSm);
export default Memo;