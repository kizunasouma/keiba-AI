"""add_se_extended_fields

SEレコード拡張フィールド: ブリンカー/変更前騎手/変更前斤量/見習/東西所属を追加

Revision ID: 781a433e2e8d
Revises: d3d69b761711
Create Date: 2026-04-12 17:29:58.495857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '781a433e2e8d'
down_revision: Union[str, None] = 'd3d69b761711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_not_exists(table: str, column_name: str, column: sa.Column) -> None:
    """カラムが存在しない場合のみ追加する（冪等性確保）"""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :col"
    ), {"table": table, "col": column_name})
    if result.fetchone() is None:
        op.add_column(table, column)


def upgrade() -> None:
    # SE拡張フィールド5カラムをrace_entriesに追加（冪等）
    _add_column_if_not_exists('race_entries', 'blinker_code',
        sa.Column('blinker_code', sa.SmallInteger(), nullable=True))
    _add_column_if_not_exists('race_entries', 'prev_jockey_code',
        sa.Column('prev_jockey_code', sa.String(length=5), nullable=True))
    _add_column_if_not_exists('race_entries', 'prev_weight_carry',
        sa.Column('prev_weight_carry', sa.Numeric(precision=4, scale=1), nullable=True))
    _add_column_if_not_exists('race_entries', 'apprentice_code',
        sa.Column('apprentice_code', sa.SmallInteger(), nullable=True))
    _add_column_if_not_exists('race_entries', 'belong_region',
        sa.Column('belong_region', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    # 追加したカラムを削除
    op.drop_column('race_entries', 'belong_region')
    op.drop_column('race_entries', 'apprentice_code')
    op.drop_column('race_entries', 'prev_weight_carry')
    op.drop_column('race_entries', 'prev_jockey_code')
    op.drop_column('race_entries', 'blinker_code')
