import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgOffice = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M3.75 19.25H14.25M3.75 19.25V5.75C3.75 4.64543 4.64543 3.75 5.75 3.75H12.25C13.3546 3.75 14.25 4.64543 14.25 5.75V8M3.75 19.25H1.75M14.25 19.25V8M14.25 19.25H20.25M14.25 8H18.25C19.3546 8 20.25 8.89543 20.25 10V19.25M20.25 19.25H22.25M10.25 8.75H7.75M7.75 12.75H10.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgOffice);
export default Memo;