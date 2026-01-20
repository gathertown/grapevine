import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgTestTube = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M20.5 10.23L13.77 3.5M19.379 9.10598L8.91396 19.571C7.67653 20.8095 5.6694 20.8103 4.4309 19.5729L4.42896 19.571C3.19046 18.3335 3.18959 16.3264 4.42701 15.0879L14.894 4.62097M7.00995 12.5H15.9799" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgTestTube);
export default Memo;