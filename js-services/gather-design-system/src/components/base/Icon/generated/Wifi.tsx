import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgWifi = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M11.999 19.25C11.792 19.25 11.624 19.418 11.626 19.625C11.625 19.832 11.793 20 12 20C12.207 20 12.375 19.832 12.375 19.625C12.375 19.418 12.207 19.25 11.999 19.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M4.59099 12C8.68299 8.247 15.316 8.247 19.408 12M1.59399 7.804C7.34099 2.732 16.659 2.732 22.406 7.804M7.57899 15.821C10.02 13.393 13.979 13.393 16.42 15.821" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgWifi);
export default Memo;