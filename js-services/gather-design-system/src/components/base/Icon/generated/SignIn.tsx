import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSignIn = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M16 12H4M16 12L10.999 7M16 12L10.999 17.001M16 4H18C19.105 4 20 4.895 20 6V18C20 19.105 19.105 20 18 20H16" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSignIn);
export default Memo;