import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgStyles = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.75 20C13.743 19.034 14.527 18.25 15.493 18.25C16.466 18.25 17.25 19.034 17.25 20M13.75 20C13.75 20.966 14.534 21.75 15.5 21.75C16.466 21.75 17.25 20.966 17.25 20M13.75 20H3M17.25 20H21M19 15H5C3.895 15 3 14.105 3 13V5C3 3.895 3.895 3 5 3H19C20.105 3 21 3.895 21 5V13C21 14.105 20.105 15 19 15Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgStyles);
export default Memo;