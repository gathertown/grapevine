import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChevronLeftSm = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M10.2197 11.4697C9.92677 11.7626 9.92677 12.2374 10.2197 12.5303L12.7197 15.0303C13.0126 15.3232 13.4874 15.3232 13.7803 15.0303C14.0732 14.7374 14.0732 14.2626 13.7803 13.9697L11.8107 12L13.7803 10.0303C14.0732 9.7374 14.0732 9.2626 13.7803 8.9697C13.4874 8.6768 13.0126 8.6768 12.7197 8.9697L10.2197 11.4697Z" fill="currentColor" /></svg>;
const Memo = memo(SvgChevronLeftSm);
export default Memo;