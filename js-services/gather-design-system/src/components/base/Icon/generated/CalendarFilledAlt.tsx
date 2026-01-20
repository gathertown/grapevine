import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCalendarFilledAlt = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M7.75 2C8.16421 2 8.5 2.33579 8.5 2.75V4H15.5V2.75C15.5 2.33579 15.8358 2 16.25 2C16.6642 2 17 2.33579 17 2.75V4H18.25C19.7688 4 21 5.23122 21 6.75V18.25C21 19.7688 19.7688 21 18.25 21H5.75C4.23122 21 3 19.7688 3 18.25V6.75C3 5.23122 4.23122 4 5.75 4H7V2.75C7 2.33579 7.33579 2 7.75 2ZM4.5 10.5V18.25C4.5 18.9404 5.05964 19.5 5.75 19.5H18.25C18.9404 19.5 19.5 18.9404 19.5 18.25V10.5H4.5Z" fill="currentColor" /></svg>;
const Memo = memo(SvgCalendarFilledAlt);
export default Memo;