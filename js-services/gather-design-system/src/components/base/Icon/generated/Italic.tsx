import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgItalic = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.5 6L10.5 18M14 18H7M10 6H17" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgItalic);
export default Memo;