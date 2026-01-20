import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgHome = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M9.5 20.5V16C9.5 14.619 10.619 13.5 12 13.5V13.5C13.381 13.5 14.5 14.619 14.5 16V20.5H20V11.914C20 11.384 19.789 10.875 19.414 10.5L12.707 3.79301C12.316 3.40201 11.683 3.40201 11.293 3.79301L4.586 10.5C4.211 10.875 4 11.384 4 11.914V20.5H9.5Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgHome);
export default Memo;