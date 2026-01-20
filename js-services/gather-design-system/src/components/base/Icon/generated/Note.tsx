import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgNote = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M14.9962 20.9963V16.9963C14.9962 15.8913 15.8912 14.9963 16.9962 14.9963H20.9962M18.1682 19.8243L20.1182 17.8743C20.6802 17.3123 20.9962 16.5493 20.9962 15.7533V6.99628C20.9962 4.78728 19.2052 2.99628 16.9962 2.99628H6.99622C4.78722 2.99628 2.99622 4.78728 2.99622 6.99628V16.9963C2.99622 19.2053 4.78722 20.9963 6.99622 20.9963H15.3392C16.4002 20.9963 17.4172 20.5753 18.1682 19.8243Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgNote);
export default Memo;