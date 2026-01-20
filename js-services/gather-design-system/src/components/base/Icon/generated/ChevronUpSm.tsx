import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChevronUpSm = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M12.5303 10.2197C12.2374 9.92677 11.7626 9.92677 11.4697 10.2197L8.96967 12.7197C8.67678 13.0126 8.67678 13.4874 8.96967 13.7803C9.26256 14.0732 9.73744 14.0732 10.0303 13.7803L12 11.8107L13.9697 13.7803C14.2626 14.0732 14.7374 14.0732 15.0303 13.7803C15.3232 13.4874 15.3232 13.0126 15.0303 12.7197L12.5303 10.2197Z" fill="currentColor" /></svg>;
const Memo = memo(SvgChevronUpSm);
export default Memo;