from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Department, Deployment, UseCase, User
from app.schemas import DepartmentDetail, DepartmentOut, UseCaseOut, UserOut
from app.security import get_current_user

router = APIRouter(tags=["departments"], dependencies=[Depends(get_current_user)])


async def _department(session: AsyncSession, code: str) -> Department:
    dept = (await session.execute(select(Department).where(Department.code == code.upper()))).scalar_one_or_none()
    if dept is None:
        raise HTTPException(404, f"No department with code {code}")
    return dept


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(Department).order_by(Department.id))).scalars().all()


@router.get("/departments/{code}", response_model=DepartmentDetail)
async def get_department(code: str, session: AsyncSession = Depends(get_session)):
    dept = await _department(session, code)

    async def rows(model):
        return (await session.execute(select(model).where(model.department_id == dept.id).order_by(model.id))).scalars().all()

    return DepartmentDetail(
        **DepartmentOut.model_validate(dept).model_dump(),
        users=await rows(User),
        use_cases=await rows(UseCase),
        deployments=await rows(Deployment),
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(department: str | None = None, reviewers_only: bool = False, session: AsyncSession = Depends(get_session)):
    query = select(User).order_by(User.department_id, User.id)
    if department:
        query = query.where(User.department_id == (await _department(session, department)).id)
    if reviewers_only:
        query = query.where(User.role == "reviewer")
    return (await session.execute(query)).scalars().all()


@router.get("/use-cases", response_model=list[UseCaseOut])
async def list_use_cases(department: str | None = None, session: AsyncSession = Depends(get_session)):
    query = select(UseCase).order_by(UseCase.id)
    if department:
        query = query.where(UseCase.department_id == (await _department(session, department)).id)
    return (await session.execute(query)).scalars().all()


@router.get("/use-cases/{code}", response_model=UseCaseOut)
async def get_use_case(code: str, session: AsyncSession = Depends(get_session)):
    use_case = (await session.execute(select(UseCase).where(UseCase.code == code.upper()))).scalar_one_or_none()
    if use_case is None:
        raise HTTPException(404, f"No use case with code {code}")
    return use_case
