import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSend = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.45214 10.8687L20.9997 4.44532M8.97026 10.8627L3.84348 5.43678C3.24097 4.79911 3.69304 3.75 4.57035 3.75H20.5045C21.2772 3.75 21.758 4.58899 21.3673 5.25564L13.1848 19.2171C12.7385 19.9785 11.5965 19.8306 11.3589 18.9806L9.20648 11.2803C9.16279 11.124 9.08172 10.9807 8.97026 10.8627Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="square" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSend);
export default Memo;