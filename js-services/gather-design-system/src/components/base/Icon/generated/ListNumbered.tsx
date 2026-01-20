import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgListNumbered = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8.99875 6.43668H20.0033M20.0033 12H8.99875M8.99875 17.5633H20.0033M4.25 9V4L3 5.25M3 15C3 14.4477 3.44772 14 4 14H4.61448C5.1433 14 5.61278 14.3384 5.78 14.8401C5.91647 15.2495 5.82812 15.7005 5.54727 16.0282L3 19H6M3 9H5.5" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgListNumbered);
export default Memo;