import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgRecordFilled = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.3639 5.63604C21.8787 9.15076 21.8787 14.8492 18.3639 18.3639C14.8492 21.8787 9.15074 21.8787 5.63604 18.3639C2.12132 14.8492 2.12132 9.15074 5.63604 5.63604C9.15076 2.12132 14.8492 2.12132 18.3639 5.63604Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M13.7678 10.2322L13.7678 10.2322C14.7441 11.2086 14.7441 12.7915 13.7678 13.7678L13.7678 13.7678C12.7914 14.7441 11.2085 14.7441 10.2322 13.7678L10.2322 13.7678C9.25592 12.7914 9.25593 11.2085 10.2322 10.2322L10.2322 10.2322C11.2086 9.25592 12.7915 9.25593 13.7678 10.2322Z" stroke="currentColor" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgRecordFilled);
export default Memo;