import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgStars = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M1.75 9C6.78472 9 9 6.78472 9 1.75C9 6.78472 11.2153 9 16.25 9C11.2153 9 9 11.2153 9 16.25C9 11.2153 6.78472 9 1.75 9Z" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" /><path fillRule="evenodd" clipRule="evenodd" d="M12.75 17.5C16.0486 17.5 17.5 16.0486 17.5 12.75C17.5 16.0486 18.9514 17.5 22.25 17.5C18.9514 17.5 17.5 18.9514 17.5 22.25C17.5 18.9514 16.0486 17.5 12.75 17.5Z" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" /></svg>;
const Memo = memo(SvgStars);
export default Memo;